"""Diagnostics support for Load Optimizer."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN


TO_REDACT = {"tariff_entity", "battery_entity", "battery_capacity_entity", "target_percent_entity"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    redacted_data = {
        key: ("REDACTED" if key in TO_REDACT else value)
        for key, value in entry.data.items()
    }
    return {
        "entry": {
            "title": entry.title,
            "data": redacted_data,
            "options": dict(entry.options),
        },
        "coordinator_data": coordinator.data if coordinator else None,
    }
