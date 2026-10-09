"""Diagnostics support for Load Optimizer."""

from __future__ import annotations

import math
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN


# Only known non-identifying settings are safe to include in a shared download.
SAFE_BOOLEAN_SETTINGS = {
    "publish_diagnostics", "publish_profile_data", "publish_cost_forecast",
}
SAFE_NUMBER_SETTINGS = {
    "scan_interval", "cost_search_hours", "cost_forecast_hours",
    "cost_forecast_interval", "cost_candidate_interval",
    "schedule_preference_weight_pence", "slot_minutes",
}
SAFE_ENUM_SETTINGS = {
    "load_type": {"learned_appliance", "ev_charging"},
    "tariff_price_unit": {"gbp_per_kwh", "p_per_kwh", "auto"},
}
SAFE_STATUSES = {
    "ready", "not_ready", "configuration_required", "not_configured", "unavailable",
    "stale", "error", "idle", "queued", "commanding", "confirmed", "completed",
    "blocked", "failed", "expired", "cancelled", "prepared", "not_prepared",
    "active", "shadow", "clean", "action_required",
}
RETIRED_ARTIFACT_ENTITIES = (
    "automation.load_optimizer_recovery_watchdog",
    "input_boolean.load_optimizer_recovery_enabled",
    "input_number.load_optimizer_recovery_stale_after_minutes",
    "input_number.load_optimizer_recovery_restart_cooldown_minutes",
    "input_text.load_optimizer_recovery_addon_slug",
    "input_text.load_optimizer_recovery_status",
    "input_text.load_optimizer_recovery_message",
    "input_datetime.load_optimizer_recovery_last_restart",
    "input_button.load_optimizer_recovery_restart_now",
)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    raw = coordinator.data if coordinator and isinstance(coordinator.data, dict) else {}
    coordinator_data: dict[str, Any] = {}
    for key in ("status", "instance_count", "published_entity_count", "tariff_period_count"):
        value = raw.get(key)
        if key == "status":
            coordinator_data[key] = _status(value)
        elif isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            coordinator_data[key] = value
    for section in ("orchestration", "orchestration_migration", "price_cap", "plan", "tariff_intelligence"):
        payload = raw.get(section)
        if isinstance(payload, dict):
            coordinator_data[section] = {"status": _status(payload.get("status"))}
    if coordinator is not None:
        coordinator_data["last_update_success"] = bool(coordinator.last_update_success)
    retired_entities = [
        entity_id
        for entity_id in RETIRED_ARTIFACT_ENTITIES
        if hass.states.get(entity_id) is not None
    ]
    return {
        "entry": {
            "title": "REDACTED",
            "data": _configuration(entry.data),
            "options": _configuration(entry.options),
        },
        "coordinator_data": coordinator_data,
        "legacy_cleanup": {
            "status": "action_required" if retired_entities else "clean",
            "retired_entities": retired_entities,
            "message": (
                "Remove the listed retired recovery helpers after taking a backup."
                if retired_entities
                else "No retired Load Optimizer recovery entities were detected."
            ),
        },
    }


def _status(value: Any) -> str:
    """Do not copy unexpected error text or household data into diagnostics."""
    return value if isinstance(value, str) and value in SAFE_STATUSES else "unknown"


def _configuration(values: dict[str, Any]) -> dict[str, Any]:
    """Allowlist fields rather than trying to enumerate every possible secret."""
    result: dict[str, Any] = {}
    for key, value in values.items():
        if key in SAFE_BOOLEAN_SETTINGS and isinstance(value, bool):
            result[key] = value
        elif key in SAFE_NUMBER_SETTINGS and type(value) in (int, float) and math.isfinite(value):
            result[key] = value
        elif key in SAFE_ENUM_SETTINGS and isinstance(value, str) and value in SAFE_ENUM_SETTINGS[key]:
            result[key] = value
    return result
