"""Load Optimizer Home Assistant integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import LoadOptimizerCoordinator

LOGGER = logging.getLogger(__name__)
SERVICE_IMPORT_LEGACY_STATE = "import_legacy_state"
SERVICE_MOTHBALL_LEGACY_ADDON = "mothball_legacy_addon"
CONF_LEGACY_STATE_JSON = "legacy_state_json"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Load Optimizer services."""

    async def async_import_legacy_state(call) -> None:
        payload = call.data[CONF_LEGACY_STATE_JSON]
        for coordinator in hass.data.get(DOMAIN, {}).values():
            runtime = getattr(coordinator, "legacy_runtime", None)
            if runtime is None:
                continue
            result = await runtime.async_import_state(payload)
            await coordinator.async_request_refresh()
            hass.states.async_set(
                "sensor.load_optimizer_migration_status",
                result["status"],
                {
                    "friendly_name": "Load Optimizer Migration Status",
                    "icon": "mdi:database-import",
                    "imported_instances": result["instances"],
                    "message": "Legacy Load Optimizer state imported into integration storage.",
                },
            )
            return
        hass.states.async_set(
            "sensor.load_optimizer_migration_status",
            "no_runtime",
            {
                "friendly_name": "Load Optimizer Migration Status",
                "icon": "mdi:database-alert",
                "message": "Create a learned-appliance Load Optimizer integration entry before importing state.",
            },
        )

    async def async_mothball_legacy_addon(call) -> None:
        hass.states.async_set(
            "sensor.load_optimizer_legacy_addon_status",
            "ready_to_disable",
            {
                "friendly_name": "Load Optimizer Legacy Add-on Status",
                "icon": "mdi:archive-arrow-down",
                "message": (
                    "The integration compatibility runtime is active. After validating published "
                    "entities and automations, stop and disable the legacy Home Assistant add-on."
                ),
            },
        )
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": "load_optimizer_mothball_legacy_addon",
                "title": "Load Optimizer legacy add-on can be mothballed",
                "message": (
                    "Validate that the HACS integration is publishing the expected "
                    "sensor.load_optimizer_* entities, then stop and disable the old add-on. "
                    "Keep an add-on backup until the integration has captured at least one full cycle."
                ),
            },
            blocking=False,
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_LEGACY_STATE,
        async_import_legacy_state,
        schema=vol.Schema({vol.Required(CONF_LEGACY_STATE_JSON): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MOTHBALL_LEGACY_ADDON,
        async_mothball_legacy_addon,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Load Optimizer from a config entry."""
    coordinator = LoadOptimizerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Load Optimizer config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
