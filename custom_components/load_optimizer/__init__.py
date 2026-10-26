"""Load Optimizer Home Assistant integration."""

from __future__ import annotations

import logging
import re

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.util import dt as dt_util
from homeassistant.exceptions import ConfigEntryError

from .const import CONF_LOAD_TYPE, CONF_TARIFF_TIMEZONE, DEFAULT_TARIFF_TIMEZONE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE, PLATFORMS
from .coordinator import LoadOptimizerCoordinator
from .optimizer.state_import import MAX_STATE_BYTES

LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SERVICE_IMPORT_LEGACY_STATE = "import_legacy_state"
SERVICE_MOTHBALL_LEGACY_ADDON = "mothball_legacy_addon"
SERVICE_RECOVER = "recover"
SERVICE_PREPARE_ORCHESTRATION_MIGRATION = "prepare_orchestration_migration"
SERVICE_ACTIVATE_NATIVE_ORCHESTRATION = "activate_native_orchestration"
SERVICE_DEACTIVATE_NATIVE_ORCHESTRATION = "deactivate_native_orchestration"
CONF_LEGACY_STATE_JSON = "legacy_state_json"
OBSOLETE_CONTROL_ENTITY = re.compile(
    r"^sensor\.load_optimizer_(?!1_)[^_]+_(?:execution_status|execution_lifecycle|"
    r"last_start_attempt|last_start_program|last_start_result|last_start_failure_reason|"
    r"last_start_reason_code|last_start_reason_detail|last_start_decision_snapshot|"
    r"remote_start_blocked_programs)$"
)
NATIVE_STATUS_OBJECT_IDS = {
    "overnight_readiness": "load_optimizer_1_overnight_readiness",
    "remote_activation": "load_optimizer_1_remote_activation_check",
    "data_freshness": "load_optimizer_1_data_freshness",
    "automatic_plan_resilience": "load_optimizer_1_automatic_plan_resilience",
    "negative_price_readiness": "load_optimizer_1_negative_price_readiness",
}
RETIRED_INTEGRATION_ENTITY_IDS = {
    "sensor.load_optimizer_1_automation_package_status",
}


def _async_migrate_native_status_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Migrate only our registry entries; report IDs owned by other integrations."""
    if entry.data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE:
        return
    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    conflicts = []
    for key, object_id in NATIVE_STATUS_OBJECT_IDS.items():
        entity_id = f"sensor.{object_id}"
        unique_id = f"{entry.entry_id}_orchestration_{key}"
        existing = entity_registry.async_get(entity_id)
        if (
            (existing is not None and (existing.platform != DOMAIN or existing.config_entry_id != entry.entry_id))
            or (existing is None and hass.states.get(entity_id) is not None)
        ):
            conflicts.append(entity_id)
        if (
            existing is not None
            and existing.platform == DOMAIN
            and existing.config_entry_id == entry.entry_id
            and existing.unique_id != unique_id
            and not any(candidate.unique_id == unique_id for candidate in entries)
        ):
            entity_registry.async_update_entity(entity_id, new_unique_id=unique_id)
    issue_id = f"legacy_status_conflict_{entry.entry_id}"
    if conflicts:
        ir.async_create_issue(
            hass, DOMAIN, issue_id, is_fixable=False,
            severity=ir.IssueSeverity.WARNING, translation_key="legacy_status_conflict",
            translation_placeholders={"entities": ", ".join(conflicts)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def _async_claim_native_status_entity_ids(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Rename native status entities to package-era IDs once those IDs are free."""
    if entry.data.get(CONF_LOAD_TYPE) != LOAD_TYPE_LEARNED_APPLIANCE:
        return
    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    for key, object_id in NATIVE_STATUS_OBJECT_IDS.items():
        target_entity_id = f"sensor.{object_id}"
        unique_id = f"{entry.entry_id}_orchestration_{key}"
        native_entry = next(
            (candidate for candidate in entries if candidate.platform == DOMAIN and candidate.unique_id == unique_id),
            None,
        )
        if (
            native_entry is not None
            and native_entry.entity_id != target_entity_id
            and entity_registry.async_get(target_entity_id) is None
            and hass.states.get(target_entity_id) is None
        ):
            entity_registry.async_update_entity(
                native_entry.entity_id,
                new_entity_id=target_entity_id,
            )


def _async_remove_obsolete_control_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Remove control-only entities that were previously created for passive loads."""
    entity_registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if (
            OBSOLETE_CONTROL_ENTITY.match(registry_entry.entity_id)
            or registry_entry.entity_id in RETIRED_INTEGRATION_ENTITY_IDS
        ):
            entity_registry.async_remove(registry_entry.entity_id)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Load Optimizer services."""

    async def async_import_legacy_state(call) -> None:
        payload = call.data[CONF_LEGACY_STATE_JSON]
        for coordinator in hass.data.get(DOMAIN, {}).values():
            runtime = getattr(coordinator, "legacy_runtime", None)
            if runtime is None:
                continue
            if coordinator.orchestrator and coordinator.orchestrator.state.get("request"):
                raise ServiceValidationError("Cancel pending appliance requests before importing memory")
            try:
                result = await runtime.async_import_state(payload)
            except ValueError as error:
                raise ServiceValidationError(str(error)) from error
            await coordinator.async_request_refresh()
            await hass.services.async_call(
                "persistent_notification", "create",
                {
                    "notification_id": "load_optimizer_migration_status",
                    "title": "Load Optimizer learning imported",
                    "message": f"Legacy learning imported for instances: {', '.join(result['instances']) or 'none'}. Verify the learned run counts before retiring the add-on.",
                },
                blocking=True,
            )
            return
        raise ServiceValidationError("Create a learned-appliance Load Optimizer entry before importing state")

    async def async_mothball_legacy_addon(call) -> None:
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
        await hass.services.async_call(
            "persistent_notification", "create",
            {
                "notification_id": "load_optimizer_recovery_status",
                "title": "Load Optimizer recovery",
                "message": (
                    "Learned-appliance integration reload requested."
                    if entries
                    else "No learned-appliance Load Optimizer entry is configured."
                ),
            },
            blocking=True,
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

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_IMPORT_LEGACY_STATE,
        async_import_legacy_state,
        schema=vol.Schema({vol.Required(CONF_LEGACY_STATE_JSON): vol.All(str, vol.Length(max=MAX_STATE_BYTES))}),
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_MOTHBALL_LEGACY_ADDON,
        async_mothball_legacy_addon,
    )
    async_register_admin_service(hass, DOMAIN, SERVICE_RECOVER, async_recover)
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_PREPARE_ORCHESTRATION_MIGRATION,
        async_prepare_orchestration_migration,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_ACTIVATE_NATIVE_ORCHESTRATION,
        async_activate_native_orchestration,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_DEACTIVATE_NATIVE_ORCHESTRATION,
        async_deactivate_native_orchestration,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Load Optimizer from a config entry."""
    data = {**entry.data, **entry.options}
    local_timezone = await dt_util.async_get_time_zone(data.get(CONF_TARIFF_TIMEZONE, DEFAULT_TARIFF_TIMEZONE))
    if local_timezone is None:
        raise ConfigEntryError("Unknown tariff timezone; review the integration settings")
    _async_migrate_native_status_entities(hass, entry)
    _async_remove_obsolete_control_entities(hass, entry)
    coordinator = LoadOptimizerCoordinator(hass, entry, local_timezone=local_timezone)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    if coordinator.orchestrator:
        coordinator.orchestrator.set_update_callback(
            coordinator.async_update_orchestration_data
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_claim_native_status_entity_ids(hass, entry)
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
