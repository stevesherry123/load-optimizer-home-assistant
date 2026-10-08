"""Load Optimizer Home Assistant integration."""

from __future__ import annotations

import logging
import re
import json

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_LOAD_TYPE, DOMAIN, LOAD_TYPE_LEARNED_APPLIANCE, PLATFORMS
from .coordinator import LoadOptimizerCoordinator

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
    """Transfer stable package-era entity IDs to native status sensors."""
    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    for key, object_id in NATIVE_STATUS_OBJECT_IDS.items():
        entity_id = f"sensor.{object_id}"
        unique_id = f"{entry.entry_id}_orchestration_{key}"
        current_state = hass.states.get(entity_id)
        native_entry = next(
            (candidate for candidate in entries if candidate.unique_id == unique_id),
            None,
        )
        if native_entry is not None and native_entry.entity_id != entity_id:
            entity_registry.async_remove(native_entry.entity_id)
        existing = entity_registry.async_get(entity_id)
        if (
            existing is not None
            and existing.platform == "template"
            and existing.config_entry_id is None
            and (current_state is None or current_state.state == "unavailable")
        ):
            entity_registry.async_remove(entity_id)
            hass.states.async_remove(entity_id)
            existing = None
        if (
            existing is not None
            and existing.config_entry_id == entry.entry_id
            and existing.unique_id != unique_id
        ):
            entity_registry.async_update_entity(entity_id, new_unique_id=unique_id)


def _async_claim_native_status_entity_ids(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Rename native status entities to package-era IDs once those IDs are free."""
    entity_registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    for key, object_id in NATIVE_STATUS_OBJECT_IDS.items():
        target_entity_id = f"sensor.{object_id}"
        unique_id = f"{entry.entry_id}_orchestration_{key}"
        native_entry = next(
            (candidate for candidate in entries if candidate.unique_id == unique_id),
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

    def tariff_coordinator(entry_id):
        coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
        if coordinator is None:
            raise ServiceValidationError("Load Optimizer entry not found")
        return coordinator

    async def async_analyse_tariffs(call):
        await tariff_coordinator(call.data["entry_id"]).async_request_refresh()

    async def async_export_tariff_history(call):
        coordinator = tariff_coordinator(call.data["entry_id"])
        return await coordinator.tariff_intelligence.async_export(call.data["retention_days"])

    async def async_import_tariff_history(call):
        coordinator = tariff_coordinator(call.data["entry_id"])
        try:
            payload = json.loads(call.data["history_json"])
            result = await coordinator.tariff_intelligence.async_import(
                payload, dry_run=call.data["dry_run"], overwrite_live=call.data["overwrite_live"],
                retention_days=call.data["retention_days"])
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise ServiceValidationError("Invalid tariff-history import; no data changed") from error
        if not call.data["dry_run"]:
            await coordinator.async_request_refresh()
        return result

    async def async_generate_tariff_summary(call):
        coordinator = tariff_coordinator(call.data["entry_id"])
        analysis = coordinator.data.get("tariff_intelligence", {})
        task = hass.async_create_task(coordinator.narrative.async_generate(analysis, call.data["ai_task_entity"]))
        await task
        current = coordinator.data.get("tariff_intelligence", {})
        current["narrative"] = coordinator.narrative.snapshot(current)
        coordinator.async_update_listeners()
        return current["narrative"]

    hass.services.async_register(DOMAIN, "analyse_tariffs", async_analyse_tariffs,
        schema=vol.Schema({vol.Required("entry_id"): str}))
    hass.services.async_register(DOMAIN, "export_tariff_history", async_export_tariff_history,
        schema=vol.Schema({vol.Required("entry_id"): str,
                           vol.Optional("retention_days", default=90): vol.All(vol.Coerce(int), vol.Range(min=1, max=365))}),
        supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "import_tariff_history", async_import_tariff_history,
        schema=vol.Schema({vol.Required("entry_id"): str,
                           vol.Required("history_json"): vol.All(str, vol.Length(max=4 * 1024 * 1024)),
                           vol.Optional("dry_run", default=True): bool,
                           vol.Optional("overwrite_live", default=False): bool,
                           vol.Optional("retention_days", default=90): vol.All(vol.Coerce(int), vol.Range(min=1, max=365))}),
        supports_response=SupportsResponse.ONLY)
    hass.services.async_register(DOMAIN, "generate_tariff_summary", async_generate_tariff_summary,
        schema=vol.Schema({vol.Required("entry_id"): str,
                           vol.Required("ai_task_entity"): vol.Match(r"^ai_task\.[a-z0-9_]+$")}),
        supports_response=SupportsResponse.ONLY)

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
    _async_migrate_native_status_entities(hass, entry)
    _async_remove_obsolete_control_entities(hass, entry)
    coordinator = LoadOptimizerCoordinator(hass, entry)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    if coordinator.orchestrator:
        coordinator.orchestrator.set_update_callback(
            coordinator.async_update_orchestration_data
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if coordinator.tariff_intelligence.entity_ids:
        async def async_tariff_changed(event):
            await coordinator.async_request_refresh()

        entry.async_on_unload(async_track_state_change_event(
            hass, coordinator.tariff_intelligence.entity_ids, async_tariff_changed
        ))
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
