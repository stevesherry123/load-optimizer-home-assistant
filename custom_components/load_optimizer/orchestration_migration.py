"""Safe migration support for the legacy dishwasher automation package."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORE_VERSION = 1

LEGACY_HELPER_DOMAINS = {
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
}

LEGACY_AUTOMATION_IDS = {
    "automation.load_optimizer_1_record_run_history",
    "automation.load_optimizer_1_automatic_plan_watchdog",
    "automation.load_optimizer_1_recover_automatic_plan",
    "automation.load_optimizer_1_manual_recalculate",
    "automation.load_optimizer_1_register_automation_package_version",
    "automation.load_optimizer_1_capture_user_request",
    "automation.load_optimizer_1_auto_negative_price_request",
    "automation.load_optimizer_1_auto_normal_request",
    "automation.load_optimizer_1_cancel_user_request",
    "automation.load_optimizer_1_notify_missed_start",
    "automation.load_optimizer_1_notify_successful_start",
    "automation.load_optimizer_1_record_cycle_end",
    "automation.load_optimizer_1_reset_door_open_flag_on_cycle_start",
    "automation.load_optimizer_1_track_door_open",
    "automation.load_optimizer_1_execute_user_request",
}

EXTERNAL_DEPENDANT_AUTOMATION_IDS = {
    "automation.load_optimizer_1_set_travel_deadline_from_calendar",
    "automation.load_optimizer_1_clear_travel_deadline",
}

REQUIRED_CONTROL_HELPERS = {
    "input_boolean.load_optimizer_1_auto_mode_enabled",
    "input_boolean.load_optimizer_1_auto_negative_price_enabled",
    "input_boolean.load_optimizer_1_door_opened_since_last_cycle",
    "input_boolean.load_optimizer_1_explicit_program_override",
    "input_select.load_optimizer_1_requested_mode",
    "input_select.load_optimizer_1_override_program",
    "input_text.load_optimizer_1_bosch_device_id",
    "input_text.load_optimizer_1_bosch_power_switch",
    "input_text.load_optimizer_1_bosch_program_select",
    "input_text.load_optimizer_1_bosch_start_button",
    "input_text.load_optimizer_1_bosch_selected_program_sensor",
    "input_text.load_optimizer_1_bosch_power_state_sensor",
    "input_text.load_optimizer_1_bosch_connected_sensor",
    "input_text.load_optimizer_1_bosch_door_sensor",
    "input_text.load_optimizer_1_bosch_remote_control_sensor",
    "input_text.load_optimizer_1_bosch_remote_start_sensor",
    "input_text.load_optimizer_1_bosch_operation_state_sensor",
}


class OrchestrationMigration:
    """Capture package-owned state before native orchestration takes ownership."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = Store(
            hass,
            STORE_VERSION,
            f"{DOMAIN}.orchestration_migration.{entry.entry_id}",
        )
        self.snapshot: dict[str, Any] | None = None

    async def async_load(self) -> None:
        """Load a prior migration snapshot."""
        if self.snapshot is not None:
            return
        stored = await self.store.async_load()
        self.snapshot = stored if isinstance(stored, dict) else {}

    async def async_prepare(self) -> dict[str, Any]:
        """Persist legacy package state without changing any live entity."""
        helper_states = {
            state.entity_id: {
                "state": state.state,
                "attributes": dict(state.attributes),
            }
            for state in self.hass.states.async_all()
            if state.domain in LEGACY_HELPER_DOMAINS
            and state.object_id.startswith("load_optimizer_")
        }
        automation_states = {
            entity_id: self.hass.states.get(entity_id).state
            for entity_id in sorted(LEGACY_AUTOMATION_IDS)
            if self.hass.states.get(entity_id) is not None
        }
        dependant_automation_states = {
            entity_id: self.hass.states.get(entity_id).state
            for entity_id in sorted(EXTERNAL_DEPENDANT_AUTOMATION_IDS)
            if self.hass.states.get(entity_id) is not None
        }
        self.snapshot = {
            "prepared_at": datetime.now(timezone.utc).isoformat(),
            "helpers": helper_states,
            "automations": automation_states,
            "external_dependant_automations": dependant_automation_states,
        }
        await self.store.async_save(self.snapshot)
        return self.status

    @property
    def status(self) -> dict[str, Any]:
        """Return a compact, non-destructive migration assessment."""
        snapshot = self.snapshot or {}
        helper_states = snapshot.get("helpers", {})
        automation_states = snapshot.get("automations", {})
        dependant_automation_states = snapshot.get(
            "external_dependant_automations",
            {},
        )
        missing = sorted(REQUIRED_CONTROL_HELPERS - set(helper_states))
        prepared = bool(snapshot.get("prepared_at")) and not missing
        return {
            "status": "prepared" if prepared else "not_prepared",
            "prepared_at": snapshot.get("prepared_at"),
            "captured_helper_count": len(helper_states),
            "captured_automation_count": len(automation_states),
            "enabled_legacy_automations": sorted(
                entity_id
                for entity_id, state in automation_states.items()
                if state == "on"
            ),
            "external_dependant_automations": sorted(dependant_automation_states),
            "missing_required_helpers": missing,
            "safe_to_remove_package": False,
            "message": (
                "Legacy state is captured. Keep the package installed until native "
                "controls and execution have passed shadow-mode verification."
                if prepared
                else "Prepare migration while the legacy package is still loaded."
            ),
        }
