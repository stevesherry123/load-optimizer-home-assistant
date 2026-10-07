"""Diagnostics support for Load Optimizer."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN


TO_REDACT = {"tariff_entity", "battery_entity", "battery_capacity_entity", "target_percent_entity"}
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
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    redacted_data = {
        key: ("REDACTED" if key in TO_REDACT else value)
        for key, value in entry.data.items()
    }
    coordinator_data = dict(coordinator.data) if coordinator else None
    if coordinator_data and "legacy_entities" in coordinator_data:
        entities = coordinator_data.pop("legacy_entities")
        coordinator_data["legacy_entity_summary"] = {
            entity_id: {
                "state": payload.get("state"),
                "attribute_keys": sorted(payload.get("attributes", {})),
            }
            for entity_id, payload in entities.items()
        }
    retired_entities = [
        entity_id
        for entity_id in RETIRED_ARTIFACT_ENTITIES
        if hass.states.get(entity_id) is not None
    ]
    return {
        "entry": {
            "title": entry.title,
            "data": redacted_data,
            "options": dict(entry.options),
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
