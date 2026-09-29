"""Load Optimizer Home Assistant integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE, PLATFORMS
from .coordinator import LoadOptimizerCoordinator

LOGGER = logging.getLogger(__name__)
SERVICE_IMPORT_LEGACY_STATE = "import_legacy_state"
SERVICE_MOTHBALL_LEGACY_ADDON = "mothball_legacy_addon"
SERVICE_RECOVER = "recover"
SERVICE_PREPARE_ORCHESTRATION_MIGRATION = "prepare_orchestration_migration"
SERVICE_ACTIVATE_NATIVE_ORCHESTRATION = "activate_native_orchestration"
SERVICE_DEACTIVATE_NATIVE_ORCHESTRATION = "deactivate_native_orchestration"
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
            "ready_to_uninstall",
            {
                "friendly_name": "Load Optimizer Legacy Add-on Status",
                "icon": "mdi:archive-arrow-down",
                "message": (
                    "The integration compatibility runtime is active. After validating imported "
                    "memory and taking a post-migration backup, uninstall the stopped legacy add-on."
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
                    "Validate that the HACS integration retained the expected learned run counts "
                    "after a reload and take a post-migration backup. You can then uninstall the "
                    "stopped add-on. Keep its add-on-only backup until the integration has captured "
                    "at least one full cycle."
                ),
            },
            blocking=False,
        )

    async def async_recover(call) -> None:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.data.get(CONF_LOAD_TYPE) == LOAD_TYPE_LEARNED_APPLIANCE
        ]
        hass.states.async_set(
            "sensor.load_optimizer_recovery_status",
            "reload_requested" if entries else "no_runtime",
            {
                "friendly_name": "Load Optimizer Recovery Status",
                "icon": "mdi:reload-alert",
                "entry_count": len(entries),
                "message": (
                    "Learned-appliance integration reload requested."
                    if entries
                    else "No learned-appliance Load Optimizer entry is configured."
                ),
            },
        )
        for entry in entries:
            hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    async def async_prepare_orchestration_migration(call) -> None:
        prepared = 0
        for coordinator in hass.data.get(DOMAIN, {}).values():
            migration = getattr(coordinator, "orchestration_migration", None)
            if migration is None:
                continue
            await migration.async_prepare()
            await coordinator.async_request_refresh()
            prepared += 1
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": "load_optimizer_orchestration_migration",
                "title": "Load Optimizer orchestration migration prepared",
                "message": (
                    f"Captured package state for {prepared} learned-appliance entry. "
                    "Keep the YAML package installed until the migration sensor says "
                    "safe_to_remove_package: true."
                ),
            },
            blocking=False,
        )

    async def async_set_native_orchestration(active: bool) -> None:
        for coordinator in hass.data.get(DOMAIN, {}).values():
            orchestrator = getattr(coordinator, "orchestrator", None)
            if orchestrator is None:
                continue
            if active:
                await orchestrator.async_activate()
            else:
                await orchestrator.async_deactivate()
            await coordinator.async_request_refresh()

    async def async_activate_native_orchestration(call) -> None:
        await async_set_native_orchestration(True)

    async def async_deactivate_native_orchestration(call) -> None:
        await async_set_native_orchestration(False)

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
    hass.services.async_register(DOMAIN, SERVICE_RECOVER, async_recover)
    hass.services.async_register(
        DOMAIN,
        SERVICE_PREPARE_ORCHESTRATION_MIGRATION,
        async_prepare_orchestration_migration,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ACTIVATE_NATIVE_ORCHESTRATION,
        async_activate_native_orchestration,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DEACTIVATE_NATIVE_ORCHESTRATION,
        async_deactivate_native_orchestration,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Load Optimizer from a config entry."""
    coordinator = LoadOptimizerCoordinator(hass, entry)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    if coordinator.orchestrator:
        coordinator.orchestrator.set_update_callback(
            coordinator.async_update_orchestration_data
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if coordinator.orchestrator:
        await coordinator.orchestrator.async_start()
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload an entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Load Optimizer config entry."""
    coordinator = hass.data[DOMAIN].get(entry.entry_id)
    if coordinator and coordinator.orchestrator:
        await coordinator.orchestrator.async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Allow removal only after every integration entity has left the device."""
    entity_registry = er.async_get(hass)
    return not er.async_entries_for_device(
        entity_registry,
        device_entry.id,
        include_disabled_entities=True,
    )
